#!/usr/bin/ruby

class ExternalsProcessor


def initialize(options = {})
	@parent = options['parent'];
	ENV['PATH'] = "/opt/local/bin:#{ENV['PATH']}";
	@svn_info = svn_info_for_current_dir()
end


def svn_info_for_current_dir
	lines = shell('git svn info')
	svn_info = {};
	pairs = lines.map {|x| x.split(': ')}
	pairs.each {|k, v| svn_info[k] = v}
	return svn_info
end


def known_url?(url)
	return url == @svn_info['URL'] || (@parent && @parent.known_url?(url))
end


def shell(cmd)
	list = %x(#{cmd}).split('\n')
	status = $? >> 8
	raise "Non-zero exit status #{status} for command #{cmd}" if status != 0
	return list
end


def run
	externals = read_externals()
	p externals

return 0

end


def read_externals
#	externals = shell('git svn show-externals').reject {|x| x =~ %r%^\s*/?\s*#%}
	foo = ['/#foo', '/baz http://example.com', 'foo', 'baz2 http://xzy.com']
	externals = foo.reject {|x| x =~ %r%^\s*/?\s*#%}
	versioned_externals = externals.grep(/-r\d+\b/i)
	if !versioned_externals.empty?
		raise "Error: Found external(s) pegged to fixed revision: '#{versioned_externals.join ', '}' in '#{Dir.getwd}', don't know how to handle this.\n"
	end
	return externals.grep(%r%^/(\S+)\s+(\S+)%) {$~[1,2]}
end

#	foo = ['/#foo', 'bar', 'baz -r52', 'baz2 -r53']
#	externals = foo.reject {|x| x =~ %r%^\s*/?\s*#%}


end


processor = ExternalsProcessor.new
status = processor.run()
exit status

